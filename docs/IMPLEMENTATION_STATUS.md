# Implementation status

_Last updated: 2026-11-17. This is the handoff document: read it first when continuing the work._

## Summary

All 13 phases have a working implementation in this repository. Everything that can run without
third-party accounts was **run and tested locally**. Features that need credentials (Supabase,
LiveKit, Google, Meta, YouTube) or large model downloads (Qwen3, IndicConformer,
Indic Parler-TTS) are implemented against the official APIs and SDKs and covered by tests with mocked
services. They have **not** been exercised against the real services in this environment. The
sections below say exactly which is which.

## Verification performed

| Check | Result |
| --- | --- |
| API test suite (`services/api`, pytest) | **128 passed**: auth, isolation, vault crypto, key rotation, memory, graph orchestration, approvals (including concurrent double-approve), permissions, SSE runs, cancel/resume, scheduler (claiming, idempotency, retries, DST), voice tokens, internal voice auth, integrations, LLM providers, API hardening, ORM-to-migration sync |
| Voice agent tests (`services/voice-agent`) | **12 passed**: dispatch validation, audio preprocessing, STT/TTS adapters driven through LiveKit's public interfaces, assistant-backed LLM adapter (streaming, offline answers, outage apology, closed session) |
| Speech server tests (`services/speech`) | **8 passed** with fake engines: WAV/PCM validation, resampling, language routing, honest 503 for English without Whisper, per-sentence TTS streaming |
| Web unit tests (vitest) | **16 passed**: SSE parser (split chunks, UTF-8 Tamil), wake-word pipeline, resampler, gate cooldown and suppression, command palette ranking, JWT decoding |
| Lint and format | ruff (3 Python projects), ESLint, Prettier and `tsc --noEmit`: all clean |
| Web production build | `next build` succeeds for all 30 routes (Cache Components and PPR enabled), including standalone output |
| Supabase migration on real PostgreSQL 16 | `infrastructure/scripts/verify-migrations.sh` with `NO_PGVECTOR=1`. All tables, triggers, composite ownership FKs and RLS policies applied. Verified: cross-user FK insert rejected, RLS hides other users' rows, clients can't insert for others, read vault rows or write approvals |
| Live end-to-end (local) | API + production web server. Routing and auth protection checked for every page. Dev login and onboarding work. Assistant SSE runs against **live** Open-Meteo, RSS feeds, Nominatim and iTunes. Tamil weather question answered using the saved home location. CORS preflight and CSP verified |
| Visual UI check | Headless Chromium (WebGL via SwiftShader) screenshots with seeded demo data: every main page at 1440 px in the dark theme; dashboard, assistant, memory, history, weather and login in the light theme; dashboard at 390 px. No page errors or hydration warnings |
| Not run here | Docker builds (Docker isn't installed), real Supabase/LiveKit/Google/Meta/YouTube calls, Ollama + Qwen3, IndicConformer and Parler-TTS model inference, pgvector queries, and manual testing in Safari/Firefox and on real phones |

## Phases

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Inspection, architecture, initialization | Done | Repository was empty; monorepo created (`apps`, `services`, `packages`, `supabase`, `infrastructure`, `docs`) |
| 2. Frontend foundation, design system, auth, onboarding | Done | Next.js 16.4, Tailwind 4, shadcn (radix-nova), Supabase SSR auth + `proxy.ts`, dev-auth fallback, 4-step onboarding. Visual design: "aurora" glass UI (dark default, light "pearl" theme), WebGL 3D voice orb (`components/fx/orb-scene.tsx`, plain three.js with `THREE.Timer`, pauses off screen, CSS fallback), `motion` page/list transitions, tilt cards, ⌘K command palette; all motion respects `prefers-reduced-motion` |
| 3. Database, migrations, RLS, backend auth | Done | 16 tables, RLS on all, composite `(id, user_id)` FKs, auth trigger, pgvector HNSW; JWKS (ES256/RS256) + HS256 verification |
| 4. Assistant chat, streaming, Ollama, LangGraph | Done | LangGraph 1.2 graph (`load_context → retrieve_memory → agent ⇄ authorize/execute → persist`), resumable SSE runs, cancel, retry, Ollama/Qwen3 + OpenAI-compatible fallback + offline router |
| 5. LiveKit connection, Python agent, push-to-talk | Done (needs LiveKit creds to run) | Short-lived room-scoped tokens with explicit agent dispatch; LiveKit Agents 1.8 worker; hands-free and hold-to-talk (manual turns via RPC) |
| 6. IndicConformer STT, Qwen3, TTS, interruptions | Done (models not downloaded here) | Speech server with IndicConformer (Tamil + 21 Indic), faster-whisper for English/LID, Indic Parler-TTS streamed per sentence; VAD barge-in, explicit interrupt RPC, cancellation propagates to the API run |
| 7. Wake word and voice preferences | Done | openWakeWord on-device (ONNX Runtime Web), sensitivity, cooldown, suppression during sessions, pause in background tabs, false-trigger timeout in the agent, privacy indicator |
| 8. Gmail, location, weather, news | Done | Gmail OAuth (PKCE, encrypted refresh tokens, revoke), OSM Nominatim/Overpass with mirror fallback + backoff, Open-Meteo, RSS with dedupe |
| 9. Memory, vault, privacy controls | Done | Semantic memory (pgvector / hashing fallback), secret detection, retention; envelope-encrypted vault, audited reveals, optional re-auth window, key rotation script |
| 10. YouTube, music, WhatsApp | Done (need keys) | YouTube Data API v3 with quota-aware caching; iTunes Search (no key) / Spotify; WhatsApp Cloud API with 24h-window handling, templates, signed webhooks |
| 11. Automations, reminders, notifications | Done | DB-leased scheduler, idempotent occurrences, retries with backoff, DST-safe schedules, briefing/news/email/reminder/assistant-prompt executors, notifications |
| 12. Responsive design, PWA, performance, security hardening | Done | Mobile tab bar + voice FAB, manifest + service worker (never caches API), CSP/permissions policy, rate limits, body limits, request ids, log redaction |
| 13. Testing, deployment, documentation | Done | Tests above; Dockerfiles, docker-compose profiles, Makefile; docs for every area |

## Feature truth table

| Feature | State |
| --- | --- |
| Register / log in | Supabase email+password (needs project); dev login works locally |
| Dashboard | Working |
| Text conversation | Working (offline router without Ollama; full AI with Ollama/cloud) |
| Real-time voice | Implemented end-to-end; requires LiveKit Cloud + voice agent + speech server |
| Tamil + English speech | Tamil STT: IndicConformer. English STT: faster-whisper (IndicConformer has **no** English model). Mixed speech is transcribed in Tamil script by IndicConformer |
| Interrupt the assistant | VAD barge-in + Stop button RPC; implemented, not exercised live |
| Spoken answers | Indic Parler-TTS (Tamil "Jaya", English "Thoma"), with LiveKit Inference fallback optional |
| Push-to-talk | Hands-free and hold-to-talk modes |
| Wake word | Foreground-only, on-device (openWakeWord on ONNX Runtime Web, no account or key). The trained `hey_nexora.onnx` is committed; run `make wake-word-models` for the two shared feature models. Verified in Chromium with a fake microphone |
| Connect services | Gmail OAuth, WhatsApp Business config; YouTube/Spotify server keys |
| Email search and approved drafts | Implemented (Gmail API); approval required for drafts (configurable) and always for sends |
| Nearby places | Working with public OSM (public Overpass is often overloaded; mirror fallback + clear error) |
| Weather / news / YouTube | Weather + news working live; YouTube needs `YOUTUBE_API_KEY` |
| Memories | Working (lexical locally; semantic with Ollama `nomic-embed-text` or pgvector in production) |
| Vault | Working (local keyring); AWS KMS provider implemented, untested without AWS |
| Reminders and automations | Working (verified by scheduler tests and live reminder creation) |
| Tasks and history | Working |
| Permissions and privacy | Working (tool enable/approval toggles, retention, location sharing, export, deletion) |

## Local run, 2026-11-17

Run on an Apple M4 Max with real services: Supabase (auth), LiveKit Cloud, Ollama (`qwen3:8b`,
`nomic-embed-text`), the speech server (IndicConformer, faster-whisper `small`, Indic Parler-TTS) and
Google/YouTube keys. Text chat with tools, memory, news, weather, automations, vault and settings all
worked in a browser, and a full voice turn (greeting, speech-to-text, tool call, spoken answer) worked
end to end. Fixed along the way:

* Voice agent: `.env` is now loaded into the environment before the LiveKit worker starts (it reads
  `LIVEKIT_*` from there), and the agent connects to the room before starting the session (LiveKit
  Agents 1.8 otherwise crashes with "cannot access local participant before connecting").
* Voice starts hands-free by default (`push_to_talk_enabled` defaults to false; migration
  `20261117000000`). Before, new users got hold-to-talk with the microphone off.
* Speech server: `sentencepiece` pinned below 0.2.2, because parler-tts caps protobuf below 5.
* ⌘K palette: wrapped in `<Command>` (it crashed on open), and Enter now opens the matching page
  instead of sending the text to the assistant.
* Nearby places: a second Overpass mirror is configured by default. The public servers were often
  timing out or returning 502 during testing; the app then shows "places service is busy".
* Known: Whisper `small` can mishear Indian place names in English speech (it heard "Chennai" as
  "China" once). A larger Whisper model or a self-hosted alternative improves this.

## Known limitations and open issues

1. **IndicConformer has no English model.** English and automatic language detection depend on
   faster-whisper inside the speech server. With `SPEECH_WHISPER_MODEL` empty, `auto` falls back
   to `SPEECH_DEFAULT_LANGUAGE` (Tamil).
2. **Parler-TTS latency on CPU is high** (several seconds per sentence). Run the speech server on a
   GPU, or set `TTS_FALLBACK_MODELS` to a LiveKit Inference voice. Benchmark before choosing the
   production default (see docs/voice.md).
3. **LiveKit's semantic turn detector does not cover Tamil.** Tamil turns end on VAD silence with
   dynamic endpointing. English uses the multilingual model.
4. **Offline mode replies in English templates.** Tamil replies need a real LLM.
5. **Run buffers and rate limits are in-process.** Run a single API replica, or move both to Redis
   before scaling out (interfaces are isolated in `assistant/runs.py` and `core/rate_limit.py`).
6. **Raw voice recording is not implemented.** The `store_voice_recordings` preference is stored
   but nothing records. That needs LiveKit Egress plus a consent flow.
7. **No background push notifications.** Browser notifications only fire while the app is open.
   Web Push is the next step.
8. **The pgvector code path is untested here** (no pgvector locally); the SQL is checked by the
   schema-sync test and the migration verifier with a stand-in type.
9. **The 3D orb needs WebGL.** Without it (or with reduced motion on) the app shows the CSS orb
   instead. The WebGL bundle (three.js) is loaded lazily, only on pages that show the orb.

## Exact next steps

1. Create a Supabase project and run `supabase link && supabase db push`. Set the `SUPABASE_*` and
   `NEXT_PUBLIC_SUPABASE_*` values and confirm signup, email confirmation and the profile trigger.
2. Install Ollama and pull `qwen3:8b` and `nomic-embed-text`. Run `POST /api/v1/memories/reindex`
   for each user who has hashing-v1 memories.
3. Create a LiveKit Cloud project and fill the `LIVEKIT_*` values in `services/api/.env` and
   `services/voice-agent/.env`. Run `make voice-download-files && make dev-voice`.
4. On a GPU machine: `pip install -e 'services/speech[models]'`, start the speech server, and run a
   latency benchmark (STT RTF, TTS time to first audio) with Tamil and English samples.
5. Run `make wake-word-models` to download the wake word's shared feature models (the trained
   `hey_nexora.onnx` is committed; see `docs/voice.md` to retrain it).
6. Create a Google OAuth client (Web) with redirect `{API}/api/v1/integrations/gmail/callback` and
   add test users; set up a WhatsApp Business app; add a YouTube API key.
7. Do a browser walkthrough on desktop and mobile widths, plus an accessibility pass (keyboard,
   screen reader labels).
8. Before scaling past one API replica, add Redis-backed run buffers and rate limiting.

## Where things live

| Area | Files |
| --- | --- |
| Assistant graph | `services/api/app/assistant/graph.py`, `service.py`, `runs.py`, `tools.py`, `executor.py`, `approvals.py`, `offline.py`, `prompts.py` |
| Tools | `services/api/app/agents/*_agent.py` |
| Providers | `services/api/app/integrations/**`, `services/api/app/llm/*` |
| Security | `services/api/app/core/security.py`, `permissions.py`, `rate_limit.py`, `middleware.py`, `app/vault/encryption.py` |
| Scheduler | `services/api/app/automations/*` |
| Voice agent | `services/voice-agent/src/nexora_voice/**` |
| Speech server | `services/speech/speech_server/*` |
| Web app | `apps/web/src/app/**` (routes), `components/**`, `lib/api`, `lib/auth`, `lib/voice` |
| Schema | `supabase/migrations/20261114000000_initial_schema.sql`, `services/api/app/database/models.py` |
