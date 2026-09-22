#!/usr/bin/env bash
#
# Apply the schema to a scratch database and check its invariants hold.
#
# A constraint nobody has watched reject anything is a comment. This makes the
# schema's promises executable: it applies the migration twice (it must be safe
# to re-run), inserts a working happy path, and then checks that every statement
# the schema is supposed to refuse is refused.
#
# Needs a running Postgres. DATABASE_URL points at one -- it creates and drops
# its own scratch database -- or --local uses what `supabase start` serves.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
[ "${1:-}" = "--local" ] && shift && : "${DATABASE_URL:=postgresql://postgres:postgres@127.0.0.1:54322/postgres}"
admin="${DATABASE_URL:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}"
scratch="harness_schema_test_$$"

# Swap the database name and keep everything else. A connection URL may carry a
# query string (?host=/tmp for a unix socket), and cutting it at the last slash
# turns that into part of the database name.
base_url=$(python3 -c 'import sys;from urllib.parse import urlsplit,urlunsplit;p=urlsplit(sys.argv[1]);print(urlunsplit(p._replace(path="/"+sys.argv[2])))' "$admin" "$scratch")

psql "$admin" -q -c "create database $scratch;"
trap 'psql "$admin" -q -c "drop database if exists '"$scratch"';" >/dev/null 2>&1 || true' EXIT

# The bits of Supabase the migration leans on, stubbed so the schema can be
# checked against a bare Postgres rather than only against a real project.
psql "$base_url" -q <<'SQL'
create schema if not exists auth;
create table auth.users (id uuid primary key default gen_random_uuid(), email text);
create or replace function auth.uid() returns uuid language sql stable as $$ select null::uuid $$;
do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
create extension if not exists pgcrypto;
SQL

echo "applying the migration twice -- it has to be safe to re-run"
DATABASE_URL="$base_url" "$here/scripts/apply-schema.sh" > /dev/null
DATABASE_URL="$base_url" "$here/scripts/apply-schema.sh" > /dev/null

echo "checking the invariants"
output=$(psql "$base_url" -f "$here/supabase/tests/invariants.sql" 2>&1 || true)
rejected=$(printf '%s\n' "$output" | grep -c 'ERROR:' || true)
expected=7

printf '%s\n' "$output" | grep -E '^---|^[0-9]\.|ERROR:' | sed 's/^psql.*ERROR:  /   -> rejected: /'

echo
if [ "$rejected" -ne "$expected" ]; then
  echo "FAIL: expected $expected statements to be rejected, $rejected were." >&2
  echo "An invariant that stopped biting is worse than one that never existed." >&2
  exit 1
fi
echo "OK: $rejected of $expected refused, happy path accepted"
