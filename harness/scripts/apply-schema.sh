#!/usr/bin/env bash
#
# Apply the harness schema to a Supabase project.
#
# Deliberately psql and a plain .sql file rather than `supabase db push` and a
# migration history: the schema is one file that is safe to re-run, and a
# migration chain is a thing to maintain before there is anything to migrate
# from. When the harness has real users and real data, this grows into the CLI's
# migration flow; today that would be ceremony.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
migration="$here/supabase/migrations/0001_init.sql"

local_db=0
dry_run=0
for arg in "$@"; do
  case "$arg" in
    --local)   local_db=1 ;;
    --dry-run) dry_run=1 ;;
    -h|--help)
      sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//'
      echo
      echo "usage: $0 [--local] [--dry-run]"
      echo "  DATABASE_URL must be set unless --local is given."
      exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [ ! -f "$migration" ]; then
  echo "no migration at $migration" >&2
  exit 1
fi

if [ "$local_db" -eq 1 ]; then
  # What `supabase start` serves by default.
  url="${DATABASE_URL:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}"
else
  url="${DATABASE_URL:-}"
fi

if [ "$dry_run" -eq 1 ]; then
  # A dry run reports, it does not require: someone checking what this would do
  # should not have to produce a database URL first.
  echo "would apply $migration ($(wc -l < "$migration") lines)"
  if [ -n "$url" ]; then
    echo "to ${url##*@}"          # host and database, never the password
  else
    echo "to: nowhere -- DATABASE_URL is unset and --local was not given"
  fi
  exit 0
fi

if [ -z "$url" ]; then
  echo "DATABASE_URL is not set, and --local was not given." >&2
  echo "Find it under Project Settings -> Database -> Connection string." >&2
  exit 1
fi

if ! command -v psql > /dev/null; then
  echo "psql not found. Install the postgresql client, or run the SQL in" >&2
  echo "$migration through the Supabase dashboard's SQL editor." >&2
  exit 1
fi

# ON_ERROR_STOP because a half-applied schema is worse than none: without it
# psql reports success after skipping every statement that failed.
echo "applying $(basename "$migration")"
psql "$url" --single-transaction -v ON_ERROR_STOP=1 -f "$migration"
echo "done"
