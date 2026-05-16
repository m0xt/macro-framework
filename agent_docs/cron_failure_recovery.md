# Cron failure recovery

`scripts/refresh.sh` is the production entry point. It builds local deliverables first, then runs Supabase sync, then commits tracked outputs through `~/ops/lib/cron-wrapper.sh`.

Start every incident here:

```bash
cd ~/projects/macro-framework
tail -200 .cache/launchd-refresh-daily.log 2>/dev/null || true
tail -200 .cache/launchd-refresh.log 2>/dev/null || true
cat .cache/status.json 2>/dev/null || true
uv run pytest
uv run ruff check .
```

## Supabase sync failure

`scripts/refresh.sh` builds the local dashboard/snapshot first, then runs `python -m macro_framework.sync_to_supabase latest`. Supabase-only failures are isolated: local deliverables still commit and `.cache/status.json` reports `refresh ok, supabase sync failed (<type>)`.

Failure types:
- `supabase-schema-drift` — remote schema/version no longer matches `supabase_schema.sql` + `EXPECTED_SCHEMA_VERSION`.
- `supabase-auth` — missing/invalid `SUPABASE_URL` or `SUPABASE_SERVICE_KEY`, RLS/permission/JWT problem.
- `supabase-network` — timeout, DNS, connection, or unknown transient Supabase/PostgREST failure.

Diagnose:
1. Run `uv run python -m macro_framework.sync_to_supabase doctor`.
2. If it reports schema drift, compare:
   - local `supabase_schema.sql` (`-- VERSION: N`)
   - local `src/macro_framework/sync_to_supabase.py` (`EXPECTED_SCHEMA_VERSION = N`)
   - remote `select * from macro_meta where key = 'schema_version';`
3. If columns are missing, inspect `macro_snapshots` in the Supabase SQL editor and compare with `REQUIRED_MACRO_SNAPSHOTS_COLUMNS`.
4. If auth fails, verify `.env` / launchd environment has `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` and that the key is a service-role key.

Intentional schema change procedure:
1. Update `supabase_schema.sql` with the DDL/migration and bump `-- VERSION: N` plus the `macro_meta` sentinel value.
2. Update `EXPECTED_SCHEMA_VERSION` in `src/macro_framework/sync_to_supabase.py` to the same integer.
3. Update `REQUIRED_MACRO_SNAPSHOTS_COLUMNS` if columns changed.
4. Apply the SQL in Supabase.
5. Run `uv run python -m macro_framework.sync_to_supabase doctor` until it passes.
6. Run tests: `uv run pytest` and `uv run ruff check .`.

Manual retry after fixing:

```bash
cd ~/projects/macro-framework
uv run python -m macro_framework.sync_to_supabase doctor
uv run python -m macro_framework.sync_to_supabase latest
```

If the local dashboard build succeeded earlier, do not rerun the full refresh unless data freshness matters; the latest snapshot is already on disk.

## Yahoo/FRED transient failures

Symptoms:
- `python -m macro_framework.build --no-cache` fails before `outputs/dashboard.html` is updated.
- Stack traces from `yfinance`, `requests`, FRED CSV reads, DNS, TLS, rate limits, or empty data frames.
- `.cache/status.json` reports a refresh/build failure rather than Supabase partial success.

Recovery:
1. Check whether `.cache/raw_data.pkl` exists and whether the failure only happens with `--no-cache`.
2. Retry once after a short interval; Yahoo/FRED failures are often transient.
3. If cached data is acceptable for the dispatch, run `uv run python -m macro_framework.build` without `--no-cache` and clearly record that the build used cache.
4. Do not commit a dashboard generated from suspicious partial data. Inspect `outputs/dashboard.html` timestamp and the newest `snapshots/*.json` first.
5. If a source changed its schema/ticker, patch `macro_pipeline.fetch_all_data()` or the relevant calculator, then add/update a smoke test.

## Claude CLI timeout or weekly-brief failure

Symptoms:
- Build reaches indicator/snapshot work, then fails while generating `briefs/YYYY-MM-DD/*.md`.
- Logs mention `claude`, subprocess timeout, missing CLI, auth, or tool/network errors.

Recovery:
1. Verify the CLI exists and is authenticated:
   ```bash
   command -v claude
   claude --version
   ```
2. If the failure is a timeout or transient model/tool issue, rerun:
   ```bash
   uv run python -m macro_framework.weekly_briefs --force
   ```
3. If only one brief is missing or stale, inspect the dated folder and rerun the full generator rather than hand-editing the hierarchy.
4. If Claude is unavailable but the dashboard/snapshot is valid, decide with Bob whether to commit local data without refreshed briefs. Do not fabricate brief text.

## launchd plist not loaded

Symptoms:
- No new `.cache/launchd-refresh*.log` output.
- Jobs do not appear in `launchctl list`.
- Manual `scripts/refresh.sh` works.

Diagnose:

```bash
launchctl list | grep -E 'milkroad.*macro|macro-refresh' || true
ls -l ~/Library/LaunchAgents/com.milkroad.macro-refresh*.plist
plutil -lint ~/Library/LaunchAgents/com.milkroad.macro-refresh*.plist
```

Recovery:
1. Re-run the repo bootstrap:
   ```bash
   bash scripts/setup-mac-mini.sh
   ```
2. Confirm the substituted plist paths point at the current repo.
3. Manually run `bash scripts/refresh.sh` once to verify the environment.
4. After plist or entrypoint changes, reload both jobs when safe:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.milkroad.macro-refresh.plist
   launchctl load ~/Library/LaunchAgents/com.milkroad.macro-refresh.plist
   launchctl unload ~/Library/LaunchAgents/com.milkroad.macro-refresh-daily.plist
   launchctl load ~/Library/LaunchAgents/com.milkroad.macro-refresh-daily.plist
   ```
5. If the plist is loaded but not firing, check macOS sleep/power settings and launchd logs outside the repo.

## Escalation rules

Escalate instead of guessing if:
- MRMI math or constants appear wrong but the dispatch did not ask for parameter changes.
- Supabase remote SQL must be applied and you do not have authorization.
- Data source output changed in a way that affects historical comparability.
- A dashboard build succeeds but values look implausible and no test explains the shift.
