# Harness (staged)

The generation harness the map in `.wayfinder/` is charting: content in,
pocketanim scenes out. It belongs in **its own repo** — different stack,
different lifecycle, different CI — and is staged here only until that repo
exists, because the constraint it is built against (the `.panim` format) is
defined in this one.

What is here so far is the database, which was asked for ahead of the rest.

```
harness/
  supabase/migrations/0001_init.sql   the schema
  scripts/apply-schema.sh             applies it to a project
```

## Applying it

```sh
# against a hosted project
DATABASE_URL='postgresql://postgres:...@db.<ref>.supabase.co:5432/postgres' \
  harness/scripts/apply-schema.sh

# or against a local supabase start
harness/scripts/apply-schema.sh --local

# see what it would do first
harness/scripts/apply-schema.sh --dry-run
```

The script is idempotent: the migration is written so that re-applying it is a
no-op rather than an error, which is what makes it safe to run from CI or by
hand against a project someone has already touched.
