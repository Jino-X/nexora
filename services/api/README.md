# Nexora core API

FastAPI + LangGraph service that owns authentication, user data, permissions, the assistant graph,
tools and integrations, memory, the vault and automations. Text chat, the voice agent and the
automation worker all call into the same graph.

```bash
python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env            # or: python3 ../../infrastructure/scripts/bootstrap-env.py
.venv/bin/uvicorn app.main:create_app --factory --reload --port 8000
.venv/bin/python -m pytest -q   # 128 tests, no external services needed
.venv/bin/python -m app.automations.worker      # standalone scheduler
.venv/bin/python -m app.scripts.rotate_vault_keys
```

| Path | What |
| --- | --- |
| `app/main.py` | App factory, middleware, routers, lifespan (scheduler in dev) |
| `app/config.py` | Settings, with production guards |
| `app/core/` | JWT verification, permissions, rate limits, middleware, errors, redacting logs |
| `app/assistant/` | LangGraph graph, run manager (SSE), tool registry, executor, approvals, offline router, prompts |
| `app/agents/` | Tool modules: weather, location, news, email, messaging, media, memory, vault, automation |
| `app/integrations/` | Provider adapters: Gmail, WhatsApp, OSM, Open-Meteo, RSS, YouTube, music, credentials |
| `app/llm/` | Ollama, OpenAI-compatible, fallback chain |
| `app/memory/`, `app/vault/` | Semantic memory, envelope encryption |
| `app/automations/` | Schedules, leasing scheduler, executors, briefing |
| `app/database/` | Portable models (Postgres/pgvector and SQLite), repositories, session |
| `app/api/v1/` | REST + SSE routes |
| `app/tests/` | Pytest suite with mocked HTTP and a scripted LLM |

See [docs/api.md](../../docs/api.md) and [docs/architecture.md](../../docs/architecture.md).
