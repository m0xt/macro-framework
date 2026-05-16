# Cron failure recovery

## Supabase sync failure

`scripts/refresh.sh` builds the local dashboard/snapshot first, then runs `sync_to_supabase.py latest`. Supabase-only failures are isolated: local deliverables still commit and `.cache/status.json` reports `refresh ok, supabase sync failed (<type>)`.

Failure types:
- `supabase-schema-drift` — remote schema/version no longer matches `supabase_schema.sql` + `EXPECTED_SCHEMA_VERSION`.
- `supabase-auth` — missing/invalid `SUPABASE_URL` or `SUPABASE_SERVICE_KEY`, RLS/permission/JWT problem.
- `supabase-network` — timeout, DNS, connection, or unknown transient Supabase/PostgREST failure.

Diagnose:
1. Run `uv run python sync_to_supabase.py doctor`.
2. If it reports schema drift, compare:
   - local `supabase_schema.sql` (`-- VERSION: N`)
   - local `sync_to_supabase.py` (`EXPECTED_SCHEMA_VERSION = N`)
   - remote `select * from macro_meta where key = 'schema_version';`
3. If columns are missing, inspect `macro_snapshots` in the Supabase SQL editor and compare with `REQUIRED_MACRO_SNAPSHOTS_COLUMNS`.
4. If auth fails, verify `.env` / launchd environment has `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` and that the key is a service-role key.

Intentional schema change procedure:
1. Update `supabase_schema.sql` with the DDL/migration and bump `-- VERSION: N` plus the `macro_meta` sentinel value.
2. Update `EXPECTED_SCHEMA_VERSION` in `sync_to_supabase.py` to the same integer.
3. Update `REQUIRED_MACRO_SNAPSHOTS_COLUMNS` if columns changed.
4. Apply the SQL in Supabase.
5. Run `uv run python sync_to_supabase.py doctor` until it passes.
6. Run tests: `uv run pytest` and `uv run ruff check .`.

Manual retry after fixing:
```bash
cd ~/projects/macro-framework
uv run python sync_to_supabase.py doctor
uv run python sync_to_supabase.py latest
```

If the local dashboard build succeeded earlier, do not rerun the full refresh unless data freshness matters; the latest snapshot is already on disk.
