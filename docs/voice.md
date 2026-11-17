# Voice

## Pipeline

```
Browser mic ──WebRTC──► LiveKit Cloud ──► voice agent (services/voice-agent, LiveKit Agents 1.8)
                                             │ Silero VAD (prewarmed per process)
                                             │ turn detection (semantic model + dynamic endpointing, or manual)
                                             │ STT ──HTTP──► speech server: IndicConformer (ta) / faster-whisper (en, LID)
                                             │ "LLM" ──SSE──► core API /internal/voice/turns ─► LangGraph graph (tools, approvals, memory)
                                             │ TTS ──HTTP──► speech server: Indic Parler-TTS (sentence-chunked PCM stream)
Browser speaker ◄──WebRTC── LiveKit ◄────────┘  transcripts (lk.transcription) + tool events (nexora.tool)
```

Push-to-talk and wake word share the same session: `POST /voice/sessions` creates the session
(10-minute token, private room, explicit dispatch of `nexora-voice`). The agent reads the dispatch
metadata (`voice_session_id`, owner identity, activation, turn mode, language, voice).

## Running it

1. LiveKit Cloud project → put `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` in
   `services/api/.env` **and** `services/voice-agent/.env`.
2. Use the same random value for `INTERNAL_SERVICE_KEY` (API) and `NEXORA_INTERNAL_SERVICE_KEY`
   (agent). `make env` does this for you.
3. Speech server on a GPU machine:
   `cd services/speech && pip install -e '.[models]' && uvicorn speech_server.main:create_app --factory --port 8100`.
   Set `SPEECH_API_KEY` there and the same value as `SPEECH_SERVER_KEY` for the agent.
4. `make voice-download-files` (VAD + turn detector weights), then `make dev-voice`.

## Speech recognition

| Language | Engine | Notes |
| --- | --- | --- |
| Tamil (and 21 other Indic languages) | `ai4bharat/indic-conformer-600m-multilingual` (CTC by default; `SPEECH_INDIC_DECODING=rnnt`) | Complete-utterance inference with **no partial results**. The agent declares `streaming=False`, and LiveKit's `StreamAdapter` sends each VAD-segmented utterance |
| English | faster-whisper (`SPEECH_WHISPER_MODEL=small`) | IndicConformer has no English model |
| `auto` | faster-whisper language ID, used when its probability is ≥ 0.5, else `SPEECH_DEFAULT_LANGUAGE` | Without Whisper, `auto` means Tamil |
| Tamil-English mix | IndicConformer `ta` | English words come out in Tamil script. The LLM copes well; names and technical terms may need confirming |

Preprocessing in the agent: frames are combined, downmixed and resampled to 16 kHz mono PCM16, and
near-silent utterances (RMS below about −48 dBFS) are dropped before any STT call. The server
validates the sample rate (8–48 kHz) and duration (0.15–30 s), and warms the models up at startup.

## Speech synthesis

`ai4bharat/indic-parler-tts` is controlled by a text description. The defaults are `Jaya` for Tamil
and `Thoma` for English, set per user in Settings → Voice. The server picks the language from the
script (any Tamil characters → `ta`), splits text into sentences (including the Indic danda), and
streams PCM16 at 24 kHz as each sentence finishes. Interrupting cancels the HTTP stream.

**Evaluate before choosing the production default.** Parler-TTS is autoregressive and slow on CPU.
Measure on your target hardware:

* STT real-time factor for 5 s and 15 s utterances (Tamil and English)
* TTS time to first audio for a 12-word sentence, and the realtime factor
* End-to-end turn latency: `execution_logs` rows with `event_type='voice_metrics'` hold EOU delay,
  STT, LLM time to first token, TTS time to first byte and the end-to-end sum for every turn

If Parler is too slow, set `TTS_FALLBACK_MODELS` (LiveKit Inference). Check the vendor's Tamil
support first.

## Turn detection and interruption

* **Hands-free (default):** Silero VAD plus LiveKit's `MultilingualModel`, a semantic
  end-of-utterance model, with `endpointing.mode=dynamic` (0.5–3.0 s). The model decides whether
  the sentence is complete, so a fixed silence timer is not the only signal. Tamil isn't covered by
  the 1.8 model, so Tamil turns use VAD endpointing within the same dynamic window.
* **Hold-to-talk:** `turn_detection="manual"`. The browser calls the `nexora.start_turn` and
  `nexora.end_turn` RPCs (owner-only), and the agent commits the turn on release.
* **Barge-in:** VAD-mode interruption (min 0.4 s of speech) stops TTS. False interruptions resume
  after 1.5 s. The UI's **Stop** button calls `nexora.interrupt`. Cancelling the LLM stream closes
  the SSE request, so the API cancels the run and saves the partial reply as `cancelled`.
* **Session hygiene:** a 15-minute hard limit with a spoken farewell, a 90 s idle timeout, and
  wake-word sessions with no speech within 8 s end as false triggers. The room is deleted on close.

## Wake word ("Hey Nexora")

On-device only, with [openWakeWord](https://github.com/dscripka/openWakeWord) models run by
[ONNX Runtime Web](https://onnxruntime.ai/docs/tutorials/web/) in a Web Worker. It's free and needs
no account or key. Setup:

1. `make wake-word-models` downloads openWakeWord's two shared models (`melspectrogram.onnx`,
   `embedding_model.onnx`, release v0.5.1) into `apps/web/public/wake-word/` (git-ignored).
2. A trained **Hey Nexora** model is committed as `apps/web/public/wake-word/hey_nexora.onnx`. In
   tests with synthetic voices it scored 0.81–0.97 on "Hey Nexora" in 6 of 7 accents (0.51 for an
   Australian voice saying just "hey nexora") and ≤ 0.008 on 33 look-alike phrases, against a
   default threshold of 0.4. To retrain it, use openWakeWord's
   [training notebook](https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing)
   in Google Colab (free; sign in with any Google account). Set the target phrase to `hey nexora`,
   run all the cells (under an hour), download the `.onnx` model it produces, and replace the file.
   It trains on computer-generated voices, so there's nothing to record. If it misses the name, try
   a phonetic spelling such as `hey neksora`.
3. Restart `pnpm dev`. Users turn it on in Settings → Voice and can set the sensitivity
   (0.1–0.95) and the cooldown.

To compare against a known-good model, `make wake-word-models ARGS="--test --force"` overwrites
`hey_nexora.onnx` with openWakeWord's pre-trained **Hey Jarvis** model, so saying "Hey Jarvis"
starts a session (`git checkout apps/web/public/wake-word/hey_nexora.onnx` restores the trained one).

Licences: openWakeWord's code is Apache 2.0. Its pre-trained wake word models, including Hey Jarvis,
are CC BY-NC-SA 4.0, so personal, non-commercial use only. The shared embedding model comes from
Google's speech embedding (Apache 2.0). Check the training notebook's notes on its datasets before
using a model you trained commercially.

How detection works (`apps/web/src/lib/voice/`):

* `public/audio/wake-word-capture.js`, an AudioWorklet, reads the microphone and posts blocks to
  `wake-word.worker.ts`, which resamples them to 16 kHz.
* `wake-word-pipeline.ts` is a port of openWakeWord's streaming `AudioFeatures`: per 80 ms chunk, a
  mel spectrogram (with 480 samples of left context), one embedding of the last 76 mel frames, then
  the wake word model scores the last 16 embeddings. A score at or above `1 − sensitivity` (0.5 by
  default, openWakeWord's recommended threshold) is a detection. It costs about 1–2 ms per 80 ms
  chunk.
* The models load before the microphone opens, so a missing model never triggers a permission
  prompt; Settings and the header say it isn't installed. ONNX Runtime's WebAssembly file (about
  15 MB, cached afterwards) downloads the first time the wake word starts.
* Browsers may hold audio until the user first interacts with the page; listening resumes on the
  first click or key press.
* `NEXT_PUBLIC_WAKE_WORD_MODEL_URL` points at another model file (same origin, because of the CSP),
  and setting it empty turns the wake word off for the deployment.

How it behaves:

* Microphone audio never leaves the device until a detection fires. Only then does the app request
  a token and connect to LiveKit, and a chime plays.
* The engine stops while a voice session is active and while the tab is hidden. The header indicator
  shows the state, which makes it a privacy indicator too.
* False triggers are limited by the sensitivity setting, the cooldown, and the agent ending
  wake-word sessions without speech after 8 seconds.
* **Limits:** foreground browser tabs only. Browsers suspend microphones in background tabs and on
  locked phones, so a PWA **cannot** listen continuously.

## Privacy

* No audio is stored by Nexora. Transcripts are saved as conversation messages, which follow the
  user's retention settings.
* `store_voice_recordings` is off by default and **recording is not implemented**. Adding it needs
  LiveKit Egress and an explicit consent flow.
* The agent only subscribes to the session owner's audio (`RoomOptions.participant_identity`), and
  every turn is re-authorized by the API.
