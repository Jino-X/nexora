#!/usr/bin/env bash
# Applies supabase/migrations to a throwaway PostgreSQL 15+ cluster and checks RLS isolation and
# cross-user foreign keys. Usage:
#   infrastructure/scripts/verify-migrations.sh            # needs initdb/pg_ctl/psql on PATH
#   NO_PGVECTOR=1 infrastructure/scripts/verify-migrations.sh   # stand-in for vector columns
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${WORK_DIR:-$(mktemp -d)}"
PORT="${PG_PORT:-54329}"
PG="psql -X -q -v ON_ERROR_STOP=1 -h 127.0.0.1 -p $PORT -U postgres -d nexora"

cleanup() { pg_ctl -D "$WORK/data" -m immediate stop >/dev/null 2>&1 || true; }
trap cleanup EXIT

initdb -D "$WORK/data" -U postgres --auth=trust >/dev/null
pg_ctl -D "$WORK/data" -o "-p $PORT -c listen_addresses=127.0.0.1 -c unix_socket_directories=''" -l "$WORK/pg.log" -w start >/dev/null
psql -X -q -h 127.0.0.1 -p "$PORT" -U postgres -d postgres -c "create database nexora"

$PG -f "$ROOT/infrastructure/docker/postgres-init/00-supabase-shim.sql"
for f in "$ROOT"/supabase/migrations/*.sql; do
  if [[ "${NO_PGVECTOR:-0}" == "1" ]]; then
    # Validate everything except pgvector itself when the extension isn't installed.
    sed -e '/create extension if not exists vector/d' \
        -e 's/extensions\.vector(768)/double precision[]/' \
        -e '/using hnsw/d' "$f" | $PG
  else
    $PG -f "$f"
  fi
done
echo "migrations applied"

$PG <<'SQL'
-- two users created through the auth trigger
insert into auth.users (id, email) values
  ('11111111-1111-1111-1111-111111111111', 'alice@example.com'),
  ('22222222-2222-2222-2222-222222222222', 'bob@example.com');
do $$ begin
  assert (select count(*) from public.profiles) = 2, 'auth trigger did not create profiles';
  assert (select count(*) from public.user_preferences) = 2, 'auth trigger did not create preferences';
end $$;

insert into public.conversations (id, user_id, title)
values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '11111111-1111-1111-1111-111111111111', 'Alice private');

-- cross-user reference must fail (composite FK)
do $$ begin
  begin
    insert into public.messages (conversation_id, user_id, role, content)
    values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '22222222-2222-2222-2222-222222222222', 'user', 'pwned');
    raise exception 'cross-user message insert was allowed';
  exception when foreign_key_violation then null;
  end;
end $$;

-- RLS: Bob sees nothing of Alice's
set role authenticated;
select set_config('request.jwt.claims', '{"sub":"22222222-2222-2222-2222-222222222222","role":"authenticated"}', false);
do $$ begin
  assert (select count(*) from public.conversations) = 0, 'RLS leak: Bob can see Alice conversations';
  assert (select count(*) from public.profiles) = 1, 'Bob should only see his own profile';
end $$;
-- Bob cannot insert rows for Alice
do $$ begin
  begin
    insert into public.conversations (user_id, title) values ('11111111-1111-1111-1111-111111111111', 'x');
    raise exception 'RLS allowed inserting for another user';
  exception when insufficient_privilege then null;
  end;
end $$;
-- Clients can never read vault ciphertext or write approvals
do $$ begin
  begin perform 1 from public.vault_items; raise exception 'vault readable by clients';
  exception when insufficient_privilege then null; end;
  begin insert into public.approvals (user_id, tool_name, summary, expires_at)
        values ('22222222-2222-2222-2222-222222222222', 'x', 'x', now());
        raise exception 'clients can write approvals';
  exception when insufficient_privilege then null; end;
end $$;

-- Alice sees her own conversation
select set_config('request.jwt.claims', '{"sub":"11111111-1111-1111-1111-111111111111","role":"authenticated"}', false);
do $$ begin
  assert (select count(*) from public.conversations) = 1, 'Alice cannot see her own conversation';
end $$;
reset role;
SQL
echo "RLS and ownership checks passed"
