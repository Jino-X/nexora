# Nexora voice agent

LiveKit Agents 1.8 worker that handles real-time audio: VAD, turn detection, interruption, STT and
TTS. All reasoning and actions happen in the core API, reached per turn through
`NexoraAssistantLLM`, so voice and text share one graph and one set of permissions.

```bash
python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env                                  # LIVEKIT_*, NEXORA_INTERNAL_SERVICE_KEY, SPEECH_*
.venv/bin/python -m nexora_voice.main download-files  # VAD + turn detector weights
.venv/bin/python -m nexora_voice.main dev             # or `start` in production
.venv/bin/python -m pytest -q
```

| Module | Responsibility |
| --- | --- |
| `main.py` | `AgentServer`, prewarm (VAD), entrypoint: validates dispatch metadata and builds the `AgentSession` |
| `agent/` | Agent class, tool-event relay to the browser, lifecycle (limits, idle, false-trigger timeout), fixed phrases |
| `audio/` | Utterance preprocessing (16 kHz mono), turn handling options, owner-only RPCs (interrupt, hold-to-talk) |
| `providers/stt/indic_conformer.py` | `stt.STT` adapter for the speech server (non-streaming, VAD-segmented) |
| `providers/tts/indic_tts.py` | `tts.TTS` adapter streaming PCM from Indic Parler-TTS |
| `providers/llm/nexora_api.py` | `llm.LLM` adapter that streams the core API's assistant turn |
| `providers/factory.py` | Provider selection with LiveKit Inference fallbacks |
| `orchestration/assistant_client.py` | Internal API client (SSE turns, lifecycle and metrics events) |
| `observability/metrics.py` | Per-turn latency (EOU, STT, LLM TTFT, TTS TTFB) reported to the API |

See [docs/voice.md](../../docs/voice.md).
