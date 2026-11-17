-- Nexora initial schema (Supabase / PostgreSQL 15+)
--
-- * Identity: Supabase Auth (auth.users). public.profiles.id = auth.users.id.
-- * Every user-owned table has user_id + Row Level Security.
-- * Composite (id, user_id) foreign keys make cross-user references impossible at the database
--   level (a message can only point at a conversation owned by the same user, etc.).
-- * Security-sensitive tables (vault_items, integrations, oauth_states, approvals, audit_logs,
--   execution_logs, task_runs) have NO client write policies: only the trusted API (service role /
--   database owner) writes them. Vault and credential ciphertext is not readable by clients at all.
-- * Keep in sync with services/api/app/database/models.py (checked by test_schema_sync.py).

create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------------------------
-- helpers
-- ---------------------------------------------------------------------------------------------
create or replace function public.set_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------------------------
-- profiles & preferences
-- ---------------------------------------------------------------------------------------------
create table public.profiles (
  id            uuid primary key references auth.users (id) on delete cascade,
  email         varchar(320),
  display_name  varchar(120),
  avatar_url    varchar(1024),
  timezone      varchar(64) not null default 'UTC',
  locale        varchar(16) not null default 'en',
  onboarded_at  timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create table public.user_preferences (
  id                          uuid primary key default gen_random_uuid(),
  user_id                     uuid not null unique references public.profiles (id) on delete cascade,
  preferred_language          varchar(8) not null default 'auto' check (preferred_language in ('auto', 'en', 'ta')),
  response_style              varchar(16) not null default 'concise' check (response_style in ('concise', 'detailed')),
  llm_mode                    varchar(16) not null default 'auto' check (llm_mode in ('auto', 'local', 'cloud')),
  voice_name                  varchar(64),
  voice_speaking_rate         double precision not null default 1.0,
  wake_word_enabled           boolean not null default false,
  wake_word_sensitivity       double precision not null default 0.6 check (wake_word_sensitivity between 0 and 1),
  wake_word_cooldown_seconds  integer not null default 4,
  push_to_talk_enabled        boolean not null default true,
  memory_enabled              boolean not null default true,
  memory_auto_extract         boolean not null default false,
  memory_retention_days       integer check (memory_retention_days > 0),
  conversation_retention_days integer check (conversation_retention_days > 0),
  store_voice_recordings      boolean not null default false,
  share_location              boolean not null default true,
  home_latitude               double precision check (home_latitude between -90 and 90),
  home_longitude              double precision check (home_longitude between -180 and 180),
  home_label                  varchar(200),
  news_categories             jsonb not null default '["world", "technology", "ai"]'::jsonb,
  theme                       varchar(8) not null default 'system',
  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now()
);

-- Create the profile + preferences row when a Supabase user signs up.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, email, display_name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1)))
  on conflict (id) do nothing;
  insert into public.user_preferences (user_id) values (new.id) on conflict (user_id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------------------------
-- conversations & messages
-- ---------------------------------------------------------------------------------------------
create table public.conversations (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.profiles (id) on delete cascade,
  title           varchar(200) not null default 'New conversation',
  channel         varchar(16) not null default 'text' check (channel in ('text', 'voice', 'automation')),
  archived        boolean not null default false,
  last_message_at timestamptz not null default now(),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (id, user_id)
);
create index ix_conversations_user_last on public.conversations (user_id, last_message_at desc);

create table public.messages (
  id              uuid primary key default gen_random_uuid(),
  conversation_id uuid not null,
  user_id         uuid not null references public.profiles (id) on delete cascade,
  role            varchar(16) not null check (role in ('user', 'assistant', 'system')),
  content         text not null default '',
  status          varchar(16) not null default 'complete' check (status in ('complete', 'error', 'cancelled')),
  channel         varchar(16) not null default 'text',
  run_id          varchar(64),
  tool_calls      jsonb not null default '[]'::jsonb,
  metadata        jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  foreign key (conversation_id, user_id) references public.conversations (id, user_id) on delete cascade
);
create index ix_messages_conversation_created on public.messages (conversation_id, created_at);
create index ix_messages_user on public.messages (user_id);

-- ---------------------------------------------------------------------------------------------
-- integrations (encrypted credentials; server-only)
-- ---------------------------------------------------------------------------------------------
create table public.integrations (
  id                      uuid primary key default gen_random_uuid(),
  user_id                 uuid not null references public.profiles (id) on delete cascade,
  provider                varchar(32) not null,
  status                  varchar(16) not null default 'disconnected'
                            check (status in ('connected', 'disconnected', 'error', 'pending')),
  account_label           varchar(320),
  scopes                  jsonb not null default '[]'::jsonb,
  config                  jsonb not null default '{}'::jsonb,
  credentials_ciphertext  bytea,
  credentials_wrapped_key bytea,
  credentials_key_id      varchar(200),
  token_expires_at        timestamptz,
  connected_at            timestamptz,
  last_error              text,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),
  unique (user_id, provider)
);

create table public.oauth_states (
  state         varchar(128) primary key,
  user_id       uuid not null references public.profiles (id) on delete cascade,
  provider      varchar(32) not null,
  code_verifier varchar(128) not null,
  expires_at    timestamptz not null,
  created_at    timestamptz not null default now()
);
create index ix_oauth_states_user on public.oauth_states (user_id);

create table public.tool_permissions (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references public.profiles (id) on delete cascade,
  tool_name         varchar(64) not null,
  enabled           boolean not null default true,
  requires_approval boolean not null default false,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (user_id, tool_name)
);

-- ---------------------------------------------------------------------------------------------
-- memory (pgvector)
-- ---------------------------------------------------------------------------------------------
create table public.memories (
  id                     uuid primary key default gen_random_uuid(),
  user_id                uuid not null references public.profiles (id) on delete cascade,
  kind                   varchar(32) not null default 'fact'
                           check (kind in ('profile', 'preference', 'fact', 'project', 'conversation_summary', 'note')),
  content                text not null check (char_length(content) <= 4000),
  source                 varchar(32) not null default 'user',
  source_conversation_id uuid,
  importance             smallint not null default 3 check (importance between 1 and 5),
  pinned                 boolean not null default false,
  embedding              extensions.vector(768),
  embedding_model        varchar(100),
  expires_at             timestamptz,
  last_used_at           timestamptz,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  foreign key (source_conversation_id, user_id) references public.conversations (id, user_id)
    on delete set null (source_conversation_id)
);
create index ix_memories_user on public.memories (user_id);
create index ix_memories_embedding on public.memories using hnsw (embedding extensions.vector_cosine_ops);

-- ---------------------------------------------------------------------------------------------
-- vault (envelope-encrypted; server-only)
-- ---------------------------------------------------------------------------------------------
create table public.vault_items (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references public.profiles (id) on delete cascade,
  name             varchar(120) not null,
  kind             varchar(32) not null check (kind in ('api_key', 'password', 'note', 'document', 'secret')),
  description      varchar(500),
  content_type     varchar(120),
  size_bytes       integer not null default 0,
  ciphertext       bytea not null,
  wrapped_key      bytea not null,
  key_id           varchar(200) not null,
  last_accessed_at timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (user_id, name)
);

-- ---------------------------------------------------------------------------------------------
-- automations, task runs, approvals
-- ---------------------------------------------------------------------------------------------
create table public.automation_rules (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null references public.profiles (id) on delete cascade,
  name                  varchar(120) not null,
  kind                  varchar(32) not null
                          check (kind in ('morning_briefing', 'news_summary', 'email_summary', 'reminder', 'assistant_prompt')),
  config                jsonb not null default '{}'::jsonb,
  schedule              jsonb not null,
  timezone              varchar(64) not null default 'UTC',
  enabled               boolean not null default true,
  next_run_at           timestamptz,
  pending_occurrence_at timestamptz,
  last_run_at           timestamptz,
  last_status           varchar(16),
  consecutive_failures  integer not null default 0,
  max_retries           integer not null default 2,
  locked_until          timestamptz,
  lock_token            varchar(64),
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  unique (id, user_id)
);
create index ix_automation_rules_user on public.automation_rules (user_id);
create index ix_automation_rules_due on public.automation_rules (enabled, next_run_at) where enabled;

create table public.task_runs (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.profiles (id) on delete cascade,
  automation_id   uuid,
  conversation_id uuid,
  kind            varchar(32) not null,
  title           varchar(200) not null default '',
  status          varchar(24) not null default 'queued'
                    check (status in ('queued', 'running', 'retrying', 'succeeded', 'failed', 'cancelled', 'waiting_approval')),
  idempotency_key varchar(200) not null unique,
  scheduled_for   timestamptz,
  started_at      timestamptz,
  finished_at     timestamptz,
  attempt         integer not null default 0,
  result          jsonb not null default '{}'::jsonb,
  error           text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (id, user_id),
  foreign key (automation_id, user_id) references public.automation_rules (id, user_id) on delete set null (automation_id),
  foreign key (conversation_id, user_id) references public.conversations (id, user_id) on delete set null (conversation_id)
);
create index ix_task_runs_user_created on public.task_runs (user_id, created_at desc);
create index ix_task_runs_automation on public.task_runs (automation_id);

create table public.approvals (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.profiles (id) on delete cascade,
  conversation_id uuid,
  task_run_id     uuid,
  tool_name       varchar(64) not null,
  tool_args       jsonb not null default '{}'::jsonb,
  summary         text not null,
  status          varchar(16) not null default 'pending'
                    check (status in ('pending', 'approved', 'rejected', 'expired', 'executed', 'failed')),
  expires_at      timestamptz not null,
  decided_at      timestamptz,
  result          jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  foreign key (conversation_id, user_id) references public.conversations (id, user_id) on delete set null (conversation_id),
  foreign key (task_run_id, user_id) references public.task_runs (id, user_id) on delete set null (task_run_id)
);
create index ix_approvals_user_status on public.approvals (user_id, status);

-- ---------------------------------------------------------------------------------------------
-- logs, notifications, voice, audit
-- ---------------------------------------------------------------------------------------------
create table public.execution_logs (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.profiles (id) on delete cascade,
  run_id          varchar(64),
  conversation_id uuid,
  event_type      varchar(32) not null,
  name            varchar(100) not null,
  status          varchar(16) not null,
  duration_ms     integer not null default 0,
  provider        varchar(64),
  model           varchar(100),
  input_tokens    integer not null default 0,
  output_tokens   integer not null default 0,
  details         jsonb not null default '{}'::jsonb,
  error           text,
  created_at      timestamptz not null default now(),
  foreign key (conversation_id, user_id) references public.conversations (id, user_id) on delete set null (conversation_id)
);
create index ix_execution_logs_user_created on public.execution_logs (user_id, created_at desc);

create table public.notifications (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references public.profiles (id) on delete cascade,
  kind       varchar(32) not null,
  title      varchar(200) not null,
  body       text not null default '',
  data       jsonb not null default '{}'::jsonb,
  read_at    timestamptz,
  created_at timestamptz not null default now()
);
create index ix_notifications_user_created on public.notifications (user_id, created_at desc);
create index ix_notifications_unread on public.notifications (user_id) where read_at is null;

create table public.voice_sessions (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.profiles (id) on delete cascade,
  room_name       varchar(128) not null unique,
  status          varchar(16) not null default 'created' check (status in ('created', 'active', 'ended', 'expired', 'failed')),
  activation      varchar(16) not null default 'push_to_talk' check (activation in ('push_to_talk', 'wake_word')),
  language        varchar(8) not null default 'auto',
  conversation_id uuid,
  expires_at      timestamptz not null,
  started_at      timestamptz,
  ended_at        timestamptz,
  end_reason      varchar(64),
  turn_count      integer not null default 0,
  metadata        jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  foreign key (conversation_id, user_id) references public.conversations (id, user_id) on delete set null (conversation_id)
);
create index ix_voice_sessions_user on public.voice_sessions (user_id, created_at desc);

create table public.audit_logs (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references public.profiles (id) on delete cascade,
  actor         varchar(16) not null check (actor in ('user', 'assistant', 'system')),
  action        varchar(64) not null,
  resource_type varchar(32) not null,
  resource_id   varchar(64),
  ip_address    varchar(64),
  user_agent    varchar(300),
  details       jsonb not null default '{}'::jsonb,
  created_at    timestamptz not null default now()
);
create index ix_audit_logs_user_created on public.audit_logs (user_id, created_at desc);

-- ---------------------------------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['profiles', 'user_preferences', 'conversations', 'messages', 'integrations',
                           'tool_permissions', 'memories', 'vault_items', 'automation_rules', 'task_runs',
                           'approvals', 'voice_sessions']
  loop
    execute format('create trigger set_updated_at before update on public.%I
                    for each row execute function public.set_updated_at()', t);
  end loop;
end;
$$;

-- ---------------------------------------------------------------------------------------------
-- Row Level Security
-- (select auth.uid()) is wrapped in a sub-select so Postgres evaluates it once per statement.
-- ---------------------------------------------------------------------------------------------
alter table public.profiles          enable row level security;
alter table public.user_preferences  enable row level security;
alter table public.conversations     enable row level security;
alter table public.messages          enable row level security;
alter table public.integrations      enable row level security;
alter table public.oauth_states      enable row level security;
alter table public.tool_permissions  enable row level security;
alter table public.memories          enable row level security;
alter table public.vault_items       enable row level security;
alter table public.automation_rules  enable row level security;
alter table public.task_runs         enable row level security;
alter table public.approvals         enable row level security;
alter table public.execution_logs    enable row level security;
alter table public.notifications     enable row level security;
alter table public.voice_sessions    enable row level security;
alter table public.audit_logs        enable row level security;

-- profiles / preferences: read + update own row (inserts come from the auth trigger)
create policy "profiles: read own" on public.profiles for select to authenticated
  using ((select auth.uid()) = id);
create policy "profiles: update own" on public.profiles for update to authenticated
  using ((select auth.uid()) = id) with check ((select auth.uid()) = id);

create policy "preferences: read own" on public.user_preferences for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "preferences: update own" on public.user_preferences for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- user-managed content: full CRUD on own rows
create policy "conversations: own" on public.conversations for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "messages: read own" on public.messages for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "messages: insert own user messages" on public.messages for insert to authenticated
  with check ((select auth.uid()) = user_id and role = 'user');
create policy "messages: delete own" on public.messages for delete to authenticated
  using ((select auth.uid()) = user_id);

create policy "memories: own" on public.memories for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "tool_permissions: own" on public.tool_permissions for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "automation_rules: own" on public.automation_rules for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "notifications: read own" on public.notifications for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "notifications: mark read own" on public.notifications for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "notifications: delete own" on public.notifications for delete to authenticated
  using ((select auth.uid()) = user_id);

-- read-only for the owner; written only by the trusted API
create policy "task_runs: read own" on public.task_runs for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "approvals: read own" on public.approvals for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "execution_logs: read own" on public.execution_logs for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "voice_sessions: read own" on public.voice_sessions for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "audit_logs: read own" on public.audit_logs for select to authenticated
  using ((select auth.uid()) = user_id);

-- integrations: owners may read metadata columns only. Column privileges are additive, so drop the
-- table-level grant and re-grant the safe columns (ciphertext columns stay unreadable).
create policy "integrations: read own metadata" on public.integrations for select to authenticated
  using ((select auth.uid()) = user_id);
revoke all on public.integrations from anon, authenticated;
grant select (id, user_id, provider, status, account_label, scopes, config, token_expires_at, connected_at,
              last_error, created_at, updated_at) on public.integrations to authenticated;

-- vault_items, oauth_states: no client access at all (API only).
revoke all on public.vault_items from anon, authenticated;
revoke all on public.oauth_states from anon, authenticated;

-- anonymous users never touch user data
revoke all on all tables in schema public from anon;
