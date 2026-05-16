# Dispatch runbook

Use this when Bob dispatches a focused task in `~/projects/macro-framework`. Keep scope tight: do not migrate to `src/`, do not move/archive research scripts, and do not change MRMI math unless the dispatch explicitly asks for a parameter change.

## Bob dispatched me to fix a failed refresh

1. Inspect logs and status:
   ```bash
   cd ~/projects/macro-framework
   tail -200 .cache/launchd-refresh-daily.log 2>/dev/null || true
   tail -200 .cache/launchd-refresh.log 2>/dev/null || true
   cat .cache/status.json 2>/dev/null || true
   uv run python -m macro_framework.sync_to_supabase doctor
   ```
2. Classify the failure:
   - Data/build failure: Yahoo/FRED/cache/build problem before local dashboard completed.
   - Brief failure: Claude CLI missing/auth/timeout during weekly brief generation.
   - Supabase-only failure: `supabase-auth`, `supabase-network`, or `supabase-schema-drift`; local build may still be valid.
   - launchd failure: plist not loaded or points at the wrong repo.
3. Follow `agent_docs/cron_failure_recovery.md` for the matching class.
4. If code changes are needed, run:
   ```bash
   uv run pytest
   uv run ruff check .
   ```
5. Commit only the fix and relevant docs/test updates. Do not force-push. If production math or remote Supabase state is ambiguous, escalate with exact logs.

## Bob dispatched me to update an indicator parameter

1. Find the production constant/function in `src/macro_framework/macro_pipeline.py`.
2. Confirm the requested change is intentional and not stale-doc drift.
3. Update the math in `src/macro_framework/macro_pipeline.py` only where required.
4. Update documentation/provenance:
   - `docs/architecture.md`
   - `DECISIONS.md` if the change affects project policy or parameter rationale
   - `README.md` if a front-door lock snippet changes
5. Update or add lock coverage in `tests/test_smoke.py`.
6. Run:
   ```bash
   uv run pytest
   uv run ruff check .
   ```
7. Commit and push after green tests. Never change parameters silently.

## Bob dispatched me to refresh weekly briefs

Normal build path handles stale briefs automatically:

```bash
cd ~/projects/macro-framework
uv run python -m macro_framework.build
```

Cadence semantics: briefs regenerate if the latest archive containing each brief is older than the most recent Tuesday on or before today. This means the first successful build on/after Tuesday refreshes them; later builds skip until the next Tuesday cutoff.

Force refresh only if requested:

```bash
uv run python -m macro_framework.weekly_briefs --force
```

After a brief refresh, inspect `briefs/YYYY-MM-DD/{market,economy,top}.md`, then run tests/lint if code changed. Brief-only output commits do not require changing MRMI docs.

## Bob dispatched me to add a new indicator

1. Add data retrieval to `macro_pipeline.fetch_all_data()` if the source is new.
2. Add indicator math to `src/macro_framework/macro_pipeline.py`; keep transformations deterministic and documented in code.
3. Add chart payload fields in `prepare_chart_data()`.
4. Add snapshot fields in `save_snapshot()` if downstream systems need the value.
5. Bind dashboard UI/rendering in `src/macro_framework/build.py`.
6. If Supabase needs the field, update:
   - `supabase_schema.sql` and schema version sentinel
   - `EXPECTED_SCHEMA_VERSION`
   - `REQUIRED_MACRO_SNAPSHOTS_COLUMNS`
   - row-building logic in `src/macro_framework/sync_to_supabase.py`
   - Supabase tests
7. Add/extend a lock or smoke test in `tests/test_smoke.py`.
8. Update `docs/architecture.md` and `agent_docs/repo_map.md` if ownership changed.
9. Run:
   ```bash
   uv run pytest
   uv run ruff check .
   ```

## Bob dispatched me to update Supabase sync

1. Treat `supabase_schema.sql` as the contract.
2. If schema changes, bump `-- VERSION: N`, the `macro_meta` sentinel insert/update, and `EXPECTED_SCHEMA_VERSION` together.
3. Keep `doctor` meaningful: preflight should fail before writes if the remote is stale.
4. Run `uv run pytest` locally. If remote access is available, run `uv run python -m macro_framework.sync_to_supabase doctor` after applying SQL.
5. If remote SQL cannot be applied from this session, mark the operational step blocked rather than weakening preflight.
