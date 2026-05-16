# macro-framework

## What this does

`macro-framework` ingests Yahoo/FRED macro and market data, computes the MRMI regime signal from market momentum plus macro stress (growth impulse, financial conditions, sector breadth, macro context, stress buffer), writes daily snapshots and a self-contained dashboard, syncs hot fields to Supabase, and lazily refreshes three Claude-generated weekly briefs on the first successful build on/after Tuesday.

## Repo map

| Path | Purpose |
|---|---|
| `src/macro_framework/build.py` | Main dashboard build: data fetch, indicator compute, snapshot write, brief refresh, HTML render. |
| `src/macro_framework/macro_pipeline.py` | Production data fetch, indicator math, MRMI formula, chart payload, snapshot schema. |
| `src/macro_framework/weekly_briefs.py` | Claude CLI weekly market/economy/top brief generator. |
| `src/macro_framework/sync_to_supabase.py` | Supabase doctor/latest/backfill sync with schema-version preflight. |
| `scripts/refresh.sh` | LaunchAgent refresh entry point via `~/ops/lib/cron-wrapper.sh`. |
| `scripts/com.milkroad.macro-refresh*.plist` | Tuesday pre-meeting and weekday end-of-close launchd jobs. |
| `supabase_schema.sql` | Remote schema contract; version must match `EXPECTED_SCHEMA_VERSION`. |
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
- Cron path: `scripts/refresh.sh`

## Conventions

- Python style/tooling is encoded in `pyproject.toml` (`ruff`, lenient `pyright`, `pytest`). Do not restate formatting rules in docs.
- Production Python lives under `src/macro_framework/`; run entry points with `uv run python -m macro_framework.<module>` or project scripts.
- Do not change MRMI math, constants, release lags, or dashboard semantics without updating `docs/architecture.md`, `DECISIONS.md` when relevant, and the lock tests.
- Brief cadence is lazy weekly Tuesday: the first successful build on/after Tuesday regenerates stale briefs; later builds skip until the next Tuesday cutoff.
- Supabase failures are isolated from local dashboard/snapshot commits by `scripts/refresh.sh`.

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
