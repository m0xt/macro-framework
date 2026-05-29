# macro-framework

## What this does

`macro-framework` ingests Yahoo/FRED macro and market data, computes the MRMI regime signal from market momentum plus macro stress (growth impulse, financial conditions, sector breadth, macro context, stress buffer), writes daily snapshots and a self-contained dashboard, syncs hot fields, the current week's top brief (single-row `macro_top_brief` table), and backtest stats (single-row `macro_backtest` table) to Supabase, and lazily refreshes three Claude-generated weekly briefs on the first successful build on/after Tuesday.

## Repo map

| Path | Purpose |
|---|---|
| `src/macro_framework/build.py` | Main dashboard build: data fetch, indicator compute, snapshot write, brief refresh, HTML render. |
| `src/macro_framework/macro_pipeline.py` | Production data fetch, indicator math, MRMI formula, chart payload, snapshot schema. |
| `src/macro_framework/weekly_briefs.py` | Claude CLI weekly market/economy/top brief generator. |
| `src/macro_framework/sync_to_supabase.py` | Supabase doctor/latest/backfill sync with schema-version preflight. |
| `scripts/refresh.sh` | LaunchAgent refresh entry point via `~/ops/lib/cron-wrapper.sh`. |
| `scripts/com.milkroad.macro-refresh*.plist` | Tuesday pre-meeting and weekday end-of-close launchd jobs. |
| `migrations/` | Ordered SQL migrations (`000N_*.sql`); remote schema must match the highest file and `EXPECTED_SCHEMA_VERSION`. |
| `tests/test_smoke.py` | Import/entrypoint smoke tests and MRMI parameter/invariant locks. |
| `tests/test_supabase_sync.py` | Supabase preflight/failure-isolation tests. |
| `tests/test_sync_to_supabase.py` | Legacy Supabase row-builder tests retained under pytest. |
| `briefs/` | Git-tracked weekly Claude brief archive. |
| `outputs/dashboard.html` | Current generated dashboard, latest deliverable overwritten each run. |
| `snapshots/` | Git-tracked point-in-time JSON snapshots; see `DECISIONS.md` and `agent_docs/retention.md`. |
| `docs/PRESENTATION.html` | Shareable human explainer; moved from top-level `presentation.html`. |
| `docs/architecture.md` | Human technical narrative and MRMI provenance. |
| `agent_docs/` | Agent-facing runbooks, repo map, cron recovery, secrets contract. |
| `research/analyze_*.py` | Standalone research/provenance scripts; full triage in `agent_docs/repo_map.md`. |
| `research/archive/` | Broken retired Macro Seasons research kept for history. |
| `research/optimization/` | Manual optimization/provenance utilities, not cron path. |
| `src/macro_framework/backtest_production.py` | Manual supported backtest numbers used by presentation/report docs. |
| `report/` | Supported manual monthly-report tooling, not cron path. |
| `reports/` | Tracked monthly report artifact; output-home decision deferred. |
| `GUIDE.md`, `MACRO_FRAMEWORK_ROADMAP.md` | Long-form guide and future ideas. |

## How to run

- Install/update deps: `uv sync --extra dev`
- Tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Build dashboard from cache: `uv run python -m macro_framework.build`
- Force fresh data: `uv run python -m macro_framework.build --no-cache`
- Open after build: `uv run python -m macro_framework.build --open`
- Force briefs: `uv run python -m macro_framework.weekly_briefs --force`
- Supabase preflight: `uv run python -m macro_framework.sync_to_supabase doctor`
- Supabase latest sync: `uv run python -m macro_framework.sync_to_supabase latest`
- Apply Supabase schema migrations: see "Supabase migrations" below.
- Cron path: `scripts/refresh.sh`
- LAN dashboard serve: `com.milkroad.macro-framework-serve` exposes `outputs/dashboard.html` at `http://Felixs-Mac-mini.local:8001/dashboard.html`.
- LAN iteration-surface serve: `com.milkroad.macro-framework-docs-serve` exposes `docs/index.html` at `http://Felixs-Mac-mini.local:8011/index.html`.

## Conventions

- Python style/tooling is encoded in `pyproject.toml` (`ruff`, lenient `pyright`, `pytest`). Do not restate formatting rules in docs.
- Production Python lives under `src/macro_framework/`; run entry points with `uv run python -m macro_framework.<module>` or project scripts.
- Do not change MRMI math, constants, release lags, or dashboard semantics without updating `docs/architecture.md`, `DECISIONS.md` when relevant, and the lock tests.
- Brief cadence is lazy weekly Tuesday: the first successful build on/after Tuesday regenerates stale briefs; later builds skip until the next Tuesday cutoff.
- Supabase failures are isolated from local dashboard/snapshot commits by `scripts/refresh.sh`.

## Supabase migrations

The `migrations/` directory holds ordered SQL files (`0001_*.sql`, `0002_*.sql`, ...) that together define the remote schema contract. The current state of the remote Supabase project must equal the result of applying every migration in numeric order.

There is no automated migration runner. Apply migrations **manually** in the Supabase SQL editor.

### Applying migrations to a fresh project

1. Open the Supabase dashboard → SQL Editor.
2. For each file under `migrations/`, in ascending numeric order:
   - Open `migrations/000N_*.sql` locally.
   - Paste its full contents into a new SQL Editor query.
   - Run it.
3. Run `uv run python -m macro_framework.sync_to_supabase doctor` until it reports `Supabase preflight OK (schema version N)` where `N` matches the highest migration number.

### Applying a new migration to an existing project

1. Identify the highest migration number `N` already applied (e.g. `select value from macro_meta where key = 'schema_version';` in the SQL editor, or check the file count under `migrations/` against the remote sentinel).
2. For each new file `migrations/000M_*.sql` with `M > N`, in order: open it locally, paste into the SQL editor, run.
3. The new migration must upsert `macro_meta.schema_version` to its own `M` — that bumps the sentinel.
4. Bump `EXPECTED_SCHEMA_VERSION` in `src/macro_framework/sync_to_supabase.py` to the same `M` and commit alongside the SQL file.
5. Run `uv run python -m macro_framework.sync_to_supabase doctor` to confirm the remote now reports version `M` and required columns exist.

### Authoring a new migration

1. Pick the next sequential filename: `migrations/000(N+1)_<short_change_description>.sql`.
2. Write only the delta DDL (the file is `apply once`, not idempotent for re-application against a project that already has it — keep statements forward-only).
3. At the end of the file, add:
   ```sql
   insert into macro_meta (key, value)
   values ('schema_version', '<N+1>')
   on conflict (key) do update set value = excluded.value, updated_at = now();
   ```
4. Update `EXPECTED_SCHEMA_VERSION` in `src/macro_framework/sync_to_supabase.py` to `N+1`.
5. Update `REQUIRED_MACRO_SNAPSHOTS_COLUMNS` if columns were added/renamed/removed.
6. Run `uv run pytest` and `uv run ruff check .` before committing.
7. Apply the file manually in Supabase (see above) and then run `doctor`.

If you cannot apply the SQL remotely from the current session, commit the migration + version bump and mark the operational apply step as blocked; do not weaken preflight to make `doctor` pass.

## Testing

- Fast gate: `uv run pytest`.
- Lint gate: `uv run ruff check .`.
- Smoke tests cover production imports and dry-run entry points.
- MRMI tests lock formula invariants, stress clipping, release lags, snapshot schema, and documented parameter drift.
- Sector Breadth `LOOKBACK = 90` is intentional and locked after the 2026-05-15 reconciliation; do not revert to stale 63-day docs.

## Security

- Required Supabase vars: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.
- Target secret location: `~/ops/secrets/macro-framework/.env` under git-crypt.
- Current state: code still reads project-root `.env` or process environment via `python-dotenv`; ops-secret migration is pending.
- Never commit real `.env` or service-role keys. `.env.example` is the only committed template.
- Full contract: `agent_docs/secrets.md`.

## When something breaks

Start with `agent_docs/cron_failure_recovery.md`, then use `agent_docs/dispatch_runbook.md` for task-specific workflows. If recovery is unsafe or unclear, write an incident note under `~/ops/incidents/` and stop before changing production math or forcing pushes.
