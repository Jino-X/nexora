# Nexora developer commands. Run `make help`.
SHELL := /bin/bash
PY ?= python3.13
API := services/api
VOICE := services/voice-agent
SPEECH := services/speech

.PHONY: help setup env install install-api install-voice install-speech install-web \
        dev-api dev-worker dev-web dev-voice dev-speech \
        test test-api test-voice test-speech test-web lint format typecheck build-web \
        migrate verify-migrations voice-download-files wake-word-models

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

setup: install env ## Install everything and create local .env files

env: ## Create .env files with fresh development secrets (never overwrites)
	python3 infrastructure/scripts/bootstrap-env.py

install: install-api install-voice install-speech install-web ## Install all dependencies

install-api:
	cd $(API) && $(PY) -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -e ".[dev]"

install-voice:
	cd $(VOICE) && $(PY) -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -e ".[dev]"

install-speech: ## Speech server without the model stack (add `.[models]` to load real models)
	cd $(SPEECH) && $(PY) -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -e ".[dev]"

install-web:
	pnpm install

dev-api: ## FastAPI with reload (runs the automation scheduler in-process)
	cd $(API) && .venv/bin/uvicorn app.main:create_app --factory --reload --port 8000

dev-worker: ## Standalone automation worker (set RUN_SCHEDULER_IN_API=false when using this)
	cd $(API) && .venv/bin/python -m app.automations.worker

dev-web: ## Next.js dev server
	pnpm --filter @nexora/web dev

wake-word-models: ## Download openWakeWord's shared models into apps/web/public/wake-word (add ARGS=--test for "Hey Jarvis")
	pnpm --filter @nexora/web wake-word:models $(ARGS)

voice-download-files: ## One-time download of VAD and turn-detector weights
	cd $(VOICE) && .venv/bin/python -m nexora_voice.main download-files

dev-voice: ## LiveKit voice agent (needs LIVEKIT_* and the internal key)
	cd $(VOICE) && .venv/bin/python -m nexora_voice.main dev

dev-speech: ## Speech server (needs `pip install -e '.[models]'` and model downloads)
	cd $(SPEECH) && .venv/bin/uvicorn speech_server.main:create_app --factory --port 8100

test: test-api test-voice test-speech test-web ## Run every test suite

test-api:
	cd $(API) && .venv/bin/python -m pytest -q

test-voice:
	cd $(VOICE) && .venv/bin/python -m pytest -q

test-speech:
	cd $(SPEECH) && .venv/bin/python -m pytest -q

test-web:
	pnpm --filter @nexora/web test

lint: ## Lint all projects
	cd $(API) && .venv/bin/ruff check app && .venv/bin/ruff format --check app
	cd $(VOICE) && .venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests
	cd $(SPEECH) && .venv/bin/ruff check speech_server tests && .venv/bin/ruff format --check speech_server tests
	pnpm --filter @nexora/web lint && pnpm --filter @nexora/web format:check

typecheck: ## TypeScript typecheck
	pnpm --filter @nexora/web typecheck

format: ## Auto-format all projects
	cd $(API) && .venv/bin/ruff check app --fix -q; .venv/bin/ruff format -q app
	cd $(VOICE) && .venv/bin/ruff check src tests --fix -q; .venv/bin/ruff format -q src tests
	cd $(SPEECH) && .venv/bin/ruff check speech_server tests --fix -q; .venv/bin/ruff format -q speech_server tests
	pnpm --filter @nexora/web format

build-web: ## Production build of the web app
	pnpm --filter @nexora/web build

migrate: ## Apply supabase/migrations to the linked Supabase project (Supabase CLI)
	supabase db push

verify-migrations: ## Apply migrations to a throwaway local Postgres and check RLS (NO_PGVECTOR=1 without pgvector)
	infrastructure/scripts/verify-migrations.sh
