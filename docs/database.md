# Database

Production uses **Supabase PostgreSQL** with RLS and pgvector. `supabase/migrations/` is the source
of truth. Local development uses SQLite: the API creates the same tables from the SQLAlchemy models
(`DATABASE_AUTO_CREATE=true`). `app/tests/test_api.py::test_orm_matches_supabase_migration` fails if
the two drift.

## Tables

| Table | Purpose | Client access (RLS) |
| --- | --- | --- |
| `profiles` | One row per Supabase user (`id = auth.users.id`); name, timezone, onboarding | read/update own |
| `user_preferences` | Language, style, LLM mode, voice, wake word, memory and retention, location | read/update own |
| `conversations` | Chat threads (`text`, `voice`, `automation`) | full CRUD own |
| `messages` | User and assistant messages, tool trace, cards, model metadata | read/delete own; insert own `user` messages |
| `integrations` | Per-user connections; **encrypted** credentials | read own metadata columns only |
| `oauth_states` | Single-use OAuth state + PKCE verifier (10 min) | none |
| `tool_permissions` | Per-user tool enablement and approval overrides | full CRUD own |
| `memories` | Personal memory + `vector(768)` embedding | full CRUD own |
| `vault_items` | Envelope-encrypted secrets and documents | **none** (API only) |
| `automation_rules` | Schedules, lease columns, retry state | full CRUD own |
| `task_runs` | One row per automation occurrence or approved action (`idempotency_key` UNIQUE) | read own |
| `approvals` | Pending and decided sensitive actions | read own |
| `execution_logs` | LLM calls, tool calls, automation and voice latency (usage and cost tracking) | read own |
| `notifications` | In-app notifications | read/update/delete own |
| `voice_sessions` | LiveKit sessions: room, status, turns, latency samples | read own |
| `audit_logs` | Security events (vault reveals, approvals, connections, exports) | read own |

## Ownership guarantees

* Every user-owned table has `user_id → profiles(id) ON DELETE CASCADE`. Deleting the auth user
  removes everything.
* **Composite foreign keys** `(x_id, user_id) → parent(id, user_id)` make it impossible for a row to
  reference another user's conversation, automation or task run, even through the service role.
  Nullable references use `ON DELETE SET NULL (column)` (PostgreSQL 15+).
* The API filters every query by the authenticated `user_id` (`database/repositories.py:get_owned`).
  Rows owned by someone else return 404, so their existence is not revealed. This is the primary
  control because the API connects as the database owner. RLS protects any direct PostgREST access
  with the anon/publishable key.
* Approvals, task runs, audit logs and execution logs have **no client write policies**: only the
  trusted API writes them.

## Applying migrations

```bash
supabase link --project-ref <ref>
supabase db push                          # or: make migrate
```

To check a migration locally without Supabase, use a throwaway PostgreSQL 15+ cluster:

```bash
make verify-migrations                     # needs pgvector
NO_PGVECTOR=1 make verify-migrations       # stand-in for the vector column
```

Or use the Docker profile, which loads `infrastructure/docker/postgres-init/00-supabase-shim.sql` (auth
schema, roles, `auth.uid()`) and the migration: `docker compose --profile postgres up`.

## Connecting the API

```
DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

* Session pooler (port 5432) works with the default settings.
* Transaction pooler (port 6543) needs `DATABASE_STATEMENT_CACHE_SIZE=0`, because asyncpg prepared
  statements are incompatible with transaction pooling.
* Set `DATABASE_AUTO_CREATE=false` in production.

## Embeddings

`memories.embedding` is `vector(768)` with an HNSW cosine index. The default model is Ollama
`nomic-embed-text` (768 dimensions). To use another model, change `EMBEDDING_DIMENSIONS`,
`app/database/models.py:EMBEDDING_DIMENSIONS` and the migration together, then call
`POST /api/v1/memories/reindex`. Each memory records `embedding_model`, and searches only compare
vectors from the same model.

## Retention

The automation worker's housekeeping (every ~5 minutes):

* expires pending approvals after 24 h
* deletes memories past `expires_at` (set from `memory_retention_days`)
* deletes conversations older than `conversation_retention_days`
* marks abandoned voice sessions expired and removes stale OAuth states
