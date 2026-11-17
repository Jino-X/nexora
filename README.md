# Nexora

Nexora is a personal AI assistant for text and real-time voice, in English and Tamil. It answers
questions, checks weather, news and nearby places, works with your Gmail and WhatsApp Business
number, remembers what you ask it to, keeps secrets in an encrypted vault, and runs scheduled
briefings and reminders. Anything sensitive needs your explicit approval first.

```
apps/web               Next.js 16 (App Router, Tailwind 4, shadcn/ui, TanStack Query, Zustand, LiveKit React, PWA)
services/api           FastAPI + LangGraph core: auth, data, tools, integrations, memory, vault, automations
services/voice-agent   LiveKit Agents worker: VAD, turn detection, interruption, STT/TTS adapters
services/speech        Speech server: AI4Bharat IndicConformer (STT) + Indic Parler-TTS
packages/shared-types  API contract types used by the web app
supabase/migrations    PostgreSQL schema, RLS and pgvector (source of truth for production)
infrastructure         Dockerfiles, Postgres shim, scripts
docs                   Architecture, API, database, voice, integrations, security, deployment, status
```

Start with [docs/architecture.md](docs/architecture.md) for how the pieces fit, and
[docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) for exactly what is done, verified,
or waiting on credentials.

## Quick start (no external accounts needed)

Requirements: Python 3.13 (3.11 to 3.14 work, but not 3.15 yet, because of livekit-agents), Node 20.9+ and pnpm 11.

```bash
make install      # Python venvs for api / voice-agent / speech + pnpm install
make env          # creates .env files with fresh dev secrets (never overwrites)
make dev-api      # http://localhost:8000  (docs at /docs)
make dev-web      # http://localhost:3000
```

Sign in with any email. Without Supabase configured, the API's development login is used, and the
UI says so. This works out of the box:

| Works without any keys | Needs setup |
| --- | --- |
| Text chat with streaming, retry, stop and history | **Ollama + Qwen3 8B** for real AI answers. Without it, a clearly labelled offline intent router handles weather, news, places, reminders, memory and music |
| Weather (Open-Meteo), news (RSS), places and maps (OSM), music (Apple previews) | **Supabase** for real accounts (`NEXT_PUBLIC_SUPABASE_*`, `SUPABASE_URL`) |
| Memory (lexical search; semantic with `nomic-embed-text` in Ollama) | **LiveKit** for voice (`LIVEKIT_*`), plus the voice agent and the speech server (GPU recommended) |
| Encrypted vault, automations, reminders, notifications, approvals | **Gmail** (Google OAuth client), **WhatsApp Business** (Meta Cloud API), **YouTube** (API key), **Spotify** |
| Settings, privacy controls, data export, account deletion | **Wake word** (free: `make wake-word-models`, plus a "Hey Nexora" model trained in openWakeWord's Colab notebook) |

Enable the local LLM:

```bash
ollama serve &                      # or: docker compose --profile llm up -d
ollama pull qwen3:8b && ollama pull nomic-embed-text
```

## Everything else

| Task | Command |
| --- | --- |
| All tests (API, voice agent, speech, web) | `make test` |
| Lint / format / typecheck | `make lint`, `make format`, `make typecheck` |
| Background automation worker | `make dev-worker` (set `RUN_SCHEDULER_IN_API=false`) |
| Voice agent | `make voice-download-files && make dev-voice` |
| Speech server | `cd services/speech && .venv/bin/pip install -e '.[models]' && make dev-speech` |
| Apply DB migrations to Supabase | `supabase link --project-ref <ref> && make migrate` |
| Check migrations and RLS on a throwaway Postgres | `make verify-migrations` (`NO_PGVECTOR=1` without pgvector) |
| Docker stack | `docker compose up` (profiles: `llm`, `postgres`, `voice`, `speech`) |

## Documentation

* [Architecture](docs/architecture.md): components, request flows and the assistant graph
* [API](docs/api.md): endpoints, SSE event protocol, errors and limits
* [Database](docs/database.md): schema, RLS, ownership guarantees and migrations
* [Voice](docs/voice.md): LiveKit pipeline, STT/TTS evaluation, turn detection, wake word
* [Integrations](docs/integrations.md): setup and platform rules for each provider
* [Security](docs/security.md): threat model, encryption design and key rotation
* [Deployment](docs/deployment.md): Vercel, AWS, Supabase, LiveKit Cloud, and cost estimates
* [Implementation status](docs/IMPLEMENTATION_STATUS.md): what's done, verified and pending
